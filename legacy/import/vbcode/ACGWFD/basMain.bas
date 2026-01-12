Attribute VB_Name = "basMain"
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit

'/ path to images folder
Public Const mcstrImagesPath As String = "\Images\"
Public Const mcstrTemplatesPathKey = "TemplatesPath"
Public Const mcstrSettingSection = "Settings"

'/ called on application startup
Sub Main()
    On Error GoTo err_handler
    frmMDI.Show
    
    If Len(Command$) > 0 Then
        '# load the flow specified in the command$
        frmMDI.CommandLineLoadProcess Mid$(Command$, 2, Len(Command$) - 2)
    End If
    Exit Sub
err_handler:
    reportError Err, "basMain", "main"
End Sub

Public Sub CopyPropGroup(oPGSource As PropertyGroup, oPGDest As PropertyGroup, Optional EraseUnmatchedValues As Boolean = False, Optional OverwriteExistingValues As Boolean = False, Optional EnforceSourceNames As Boolean = False)
    On Error GoTo err_handler:
    Dim oProps As Properties
    Dim oDestProps As Properties
    
    For Each oProps In oPGSource
        If oPGDest.Exists(oProps.Name) Then
            Set oDestProps = oPGDest(oProps.Name)
        Else
            Set oDestProps = oPGDest.Add(oProps.Name)
        End If
        'Debug.Print "Copying " & oProps.Name & " to " & oDestProps.Name
        CopyProps oProps, oDestProps, EraseUnmatchedValues, OverwriteExistingValues, EnforceSourceNames
        
    Next
    Exit Sub
err_handler:
    Stop
    Resume 0
End Sub
Public Sub CopyProps(oSrcProps As Properties, oDestProps As Properties, Optional EraseUnmatched As Boolean = False, Optional OverwriteExistingValues As Boolean = True, Optional EnforceSourceName As Boolean = False)
    Dim oSrcProp As Property
    Dim oDestProp As Property
    Dim colRemove As Collection
    For Each oSrcProp In oSrcProps
        If Not oDestProps.Exists(oSrcProp.Name) Then
            
            Set oDestProp = oDestProps.Add(oSrcProp.Name, oSrcProp.Value, oSrcProp.PropertyType, oSrcProp.Locked)
        Else
            
            Set oDestProp = oDestProps(oSrcProp.Name)
            If EnforceSourceName Then
                oDestProp.Name = oSrcProp.Name
            End If
        End If
        oDestProp.Locked = oSrcProp.Locked
        If OverwriteExistingValues Then
            oDestProp.Value = oSrcProp.Value
        End If
        'Debug.Print "Created " & oDestProp.Name
    Next
    If EraseUnmatched Then
        Set colRemove = New Collection
        
        For Each oDestProp In oDestProps
            If Not oSrcProps.Exists(oDestProp.Name) Then
                colRemove.Add oDestProp
            End If
        Next
        For Each oDestProp In colRemove
            oDestProps.Remove oDestProp.Name
        Next
    End If
End Sub

Public Sub AddGUIDForConvert(oProcessDef As ProcessDef)
    oProcessDef.PropertyGroup.Item("(General)").Item("Name").Locked = True
    
    Dim oTaskDef As TaskDef
    Dim oProps As Properties
    For Each oTaskDef In oProcessDef.Tasks
        Set oProps = oTaskDef.PropertyGroup.Add("(Converted)")
        oProps.Add "OriginalGUID", oTaskDef.Guid, ptString, True
    Next
    
        
End Sub
Public Function existsInCol(col As Collection, key As String) As Boolean
    On Error Resume Next
    Dim X As Variant
    X = col.Item(key)
    If Err.Number = 449 Then
        Err.Clear
        Set X = col.Item(key)
    End If
    existsInCol = Err.Number = 0
End Function
