Attribute VB_Name = "basACGWFDXML"
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

Public Sub CopyProps(oPGSource As PropertyGroup, oPGDest As PropertyGroup)
    On Error GoTo Err_Handler:
    Dim oProp As Property
    Dim oDestProp As Property
    Dim oProps As Properties
    Dim oDestProps As Properties
    
    For Each oProps In oPGSource
        If oPGDest.Exists(oProps.Name) Then
            Set oDestProps = oPGDest(oProps.Name)
        Else
            Set oDestProps = oPGDest.Add(oProps.Name)
        End If
        'Debug.Print "Copying " & oProps.Name & " to " & oDestProps.Name
        For Each oProp In oProps
            If Not oDestProps.Exists(oProp.Name) Then
                Set oDestProp = oDestProps.Add(oProp.Name, oProp.Value, oProp.PropertyType, oProp.Locked)
            Else
                Set oDestProp = oDestProps(oProp.Name)
            End If
            oDestProp.Locked = oProp.Locked
            oDestProp.Value = oProp.Value
            'Debug.Print "Created " & oDestProp.Name
        Next
    Next
    Exit Sub
Err_Handler:
    Stop
    Resume 0
End Sub

'/ iterates over xml nodes until we hit a node that is not of type NODE_COMMENT
Public Function getRealNode(oRootNode As MSXML2.IXMLDOMNode) As MSXML2.IXMLDOMNode
    Dim oNode As MSXML2.IXMLDOMNode
    If oRootNode Is Nothing Then Exit Function
    Set oNode = oRootNode
    Do Until oNode.nodeType = NODE_ELEMENT
        Set oNode = oNode.nextSibling
        If oNode Is Nothing Then Exit Function
    Loop
    Set getRealNode = oNode
End Function

