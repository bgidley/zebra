VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "XMLProcessTemplate"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
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

Public Function LoadTemplates(Path As String, oProcessTemplates As ProcessTemplates) As Boolean
    On Error GoTo Err_Handler
    Dim oProcessTemplate As ProcessTemplate
    Dim oScan As ScanPath
    Dim strFile As String
    Set oProcessTemplates = New ProcessTemplates
    Set oScan = New ScanPath
    
    oScan.StartScan Path, ".xml"
    
    Do Until oScan.FileList.Count = 0
        strFile = oScan.FileList(1)
        oScan.FileList.Remove 1
        
        If Not LoadTemplate(strFile, oProcessTemplate) Then
            Debug.Print strFile, "Bad Process Template"
            
            'MsgBox "Selected file was not a valid Process Template", vbExclamation
        Else
            oProcessTemplates.Add oProcessTemplate
        End If
    Loop
    LoadTemplates = True
    Exit Function
Err_Handler:
    stackError Err, Me, "LoadTemplates"
End Function
Private Function LoadTemplate(FileName As String, oProcessTemplate As ProcessTemplate) As Boolean
    On Error GoTo Err_Handler
    Dim oDoc As MSXML2.DOMDocument
    Dim oRoot As MSXML2.IXMLDOMNode
    Set oDoc = New MSXML2.DOMDocument
    Set oProcessTemplate = New ProcessTemplate
    
    oDoc.Load FileName
    Set oRoot = getRealNode(oDoc.firstChild)
    
    If StrComp(oRoot.nodeName, "ACGWFD.ProcessTemplate", vbTextCompare) <> 0 Then
        LoadTemplate = False
        Exit Function
    End If
    oProcessTemplate.Name = GetNodeAttr(oRoot, "name")
    
    LoadTemplate = LoadAllSettings(oProcessTemplate, oRoot)
    Exit Function
Err_Handler:
    stackError Err, Me, "LoadTemplate"
End Function

Private Function LoadAllSettings(oProcessTemplate As ProcessTemplate, oRoot As MSXML2.IXMLDOMNode) As Boolean
    On Error GoTo Err_Handler
    Dim oNode As MSXML2.IXMLDOMNode
    Dim oNewProps As Properties
    LoadAllSettings = False
    For Each oNode In oRoot.childNodes
        Select Case UCase$(oNode.nodeName)
            Case "SETTINGS"
                '# application-level settings
                If Not LoadAppSettings(oProcessTemplate, oNode) Then Exit Function
            Case Else
                '# bad XML
                Exit Function
        End Select
    Next
    LoadAllSettings = True
    Exit Function
Err_Handler:
    stackError Err, Me, "LoadAllSettings"
End Function

Private Function LoadAppSettings(oProcessTemplate As ProcessTemplate, oRoot As MSXML2.IXMLDOMNode) As Boolean
    On Error GoTo Err_Handler
    Dim oNode As MSXML2.IXMLDOMNode
    Dim fLoadOK As Boolean
    Dim oPGTemp As PropertyGroup
    
    LoadAppSettings = False
    For Each oNode In oRoot.childNodes
        fLoadOK = True
        Select Case UCase$(oNode.nodeName)
            Case "SETTING"
                Select Case UCase$(oNode.Attributes.getNamedItem("name").nodeValue)
                    Case "COMMON TASK PROPERTIES"
                        fLoadOK = LoadPropGroups(oProcessTemplate.CommonTaskProperties, oNode)
                        If Not fLoadOK Then
                            Exit Function
                        End If
                        'fLoadOK = LoadProperties(oProcessTemplate.CommonTaskProperties, oNode)
                    Case "PROCESS PROPERTIES"
                        fLoadOK = LoadPropGroups(oProcessTemplate.ProcessProperties, oNode)
                        If Not fLoadOK Then
                            Exit Function
                        End If
                        'fLoadOK = LoadProperties(oProcessTemplate.ProcessProperties, oNode)
                    Case "GUI TASK DISPLAY"
                        Set oPGTemp = New PropertyGroup
                        fLoadOK = LoadPropGroups(oPGTemp, oNode)
                        If fLoadOK Then
                            Set oProcessTemplate.GUITaskDisplay = oPGTemp(1)
                        Else
                            Exit Function
                        End If
                        'fLoadOK = LoadProperties(oProcessTemplate.GUITaskDisplay, oNode)
                    Case "COMMON ROUTING PROPERTIES"
                        fLoadOK = LoadPropGroups(oProcessTemplate.CommonRoutingProperties, oNode)
                        If Not fLoadOK Then
                            Exit Function
                        End If
                        'fLoadOK = LoadProperties(oProcessTemplate.CommonRoutingProperties, oNode)
                End Select
        End Select
        If Not fLoadOK Then
            Exit Function
        End If
    Next
    LoadAppSettings = True
    Exit Function
Err_Handler:
    stackError Err, Me, "LoadAppSettings"
End Function

Private Function LoadPropGroups(oPropGroup As PropertyGroup, oRoot As IXMLDOMNode) As Boolean
    On Error GoTo Err_Handler
    Dim oNode As IXMLDOMNode
    Dim oXMLPropPersist As XMLPropPersist
    
    Set oXMLPropPersist = New XMLPropPersist
    
    For Each oNode In oRoot.childNodes
        If Not oXMLPropPersist.XMLProperties(oPropGroup, oNode) Then Exit Function
    Next
    LoadPropGroups = True
    Exit Function
Err_Handler:
    stackError Err, Me, "LoadPropGroups"
End Function

