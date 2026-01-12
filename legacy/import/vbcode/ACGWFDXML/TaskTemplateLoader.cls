VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "TaskTemplateLoader"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
Attribute VB_Ext_KEY = "SavedWithClassBuilder6" ,"Yes"
Attribute VB_Ext_KEY = "Top_Level" ,"Yes"
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

Public Function LoadTaskTemplates(Path As String, oTemplates As TaskTemplates) As Boolean
    On Error GoTo Err_Handler
    '# scan the path for task templates
    
    Dim oScanPath As ScanPath
    Dim lngCount As Long
    Dim fLoadOK As Boolean
    
    Set oTemplates = New TaskTemplates
    
    Set oScanPath = New ScanPath
    oScanPath.StartScan Path, ".xml"
    If oScanPath.FileList.Count = 0 Then
        MsgBox Path & vbCrLf & "Arse!"
    End If
    Do Until oScanPath.FileList.Count = 0
        fLoadOK = LoadTemplateFile(oScanPath.FileList(1), oTemplates)
        If Not fLoadOK Then
            Exit Do
        End If
        oScanPath.FileList.Remove 1
    Loop
    
    LoadTaskTemplates = fLoadOK
    Exit Function
Err_Handler:
    stackError Err, Me, "LoadTaskTemplates"
End Function

Private Function LoadTemplateFile(FileName As String, oTemplates As TaskTemplates) As Boolean
    On Error GoTo Err_Handler
    Dim oDoc As MSXML2.DOMDocument
    Dim oRoot As MSXML2.IXMLDOMNode
    
    Set oDoc = New MSXML2.DOMDocument
    
    oDoc.Load FileName
    
    Set oRoot = getRealNode(oDoc.firstChild)
    
    If StrComp(oRoot.nodeName, "ACGWFD.TaskTemplate", vbTextCompare) <> 0 Then
        LoadTemplateFile = False
        Exit Function
    End If
    
    LoadTemplateFile = ProcessTaskTemplate(oRoot, oTemplates)
    Exit Function
Err_Handler:
    stackError Err, Me, "LoadTemplateFile"
End Function

Private Function ProcessTaskTemplate(oRoot As MSXML2.IXMLDOMNode, oTemplates As TaskTemplates) As Boolean
    On Error GoTo Err_Handler
    Dim oTaskTemplate As TaskTemplate
    
    '# base attribs are:
    '# name
    '# icon
    '# description
    
    Set oTaskTemplate = oTemplates.Add(GetNodeAttr(oRoot, "name"), GetNodeAttr(oRoot, "description"), GetNodeAttr(oRoot, "icon"))
    oTaskTemplate.RoutingParallel = LenientBool(GetNodeAttr(oRoot, "routingparallel"))
    ProcessTaskTemplate = ProcessTaskProperties(oRoot, oTaskTemplate)
    Exit Function
Err_Handler:
    stackError Err, Me, "ProcessTaskTemplate"
End Function

Private Function ProcessTaskProperties(oRoot As MSXML2.IXMLDOMNode, oTemplate As TaskTemplate) As Boolean
    On Error GoTo Err_Handler
    Dim oNode As IXMLDOMNode
    Dim fLoadOK As Boolean
    Dim oXMLPropPersist As XMLPropPersist
    Set oXMLPropPersist = New XMLPropPersist
    fLoadOK = True
    
    For Each oNode In oRoot.childNodes
        If StrComp(oNode.nodeName, "properties", vbTextCompare) = 0 Then
            If Not oXMLPropPersist.XMLProperties(oTemplate.PropertyGroup, oNode) Then
                Exit Function
            End If
        End If
    Next
    ProcessTaskProperties = True
    Exit Function
Err_Handler:
    stackError Err, Me, "ProcessTaskProperties"
End Function
    
